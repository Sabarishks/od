from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Needed for session management

# MongoDB Configuration
app.config["MONGO_URI"] = "mongodb://localhost:27017/od_management"
mongo = PyMongo(app)

# Ensure uploads directory exists
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- Home/Login Page ----------
@app.route("/")
def home():
    return render_template("login.html")

# ---------- Register (Profile Creation) ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.form.to_dict()
        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        role = data.get("role")  # "student" or "faculty"

        # Choose the correct collection based on role
        collection = mongo.db.students if role == "student" else mongo.db.faculty

        # Check if user already exists
        existing_user = collection.find_one({"email": email})
        if existing_user:
            return jsonify({"error": "User already exists!"}), 400

        # Hash password before storing
        hashed_password = generate_password_hash(password)

        # Insert user into the correct database collection
        collection.insert_one({
            "name": name,
            "email": email,
            "password": hashed_password,
            "role": role
        })

        return jsonify({"message": "Registration successful!"}), 201

    return render_template("register.html")

# ---------- Login ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # Check if user exists in either students or faculty collection
        user = mongo.db.students.find_one({"email": email}) or mongo.db.faculty.find_one({"email": email})

        if user and check_password_hash(user["password"], password):
            session["user"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "student":
                return redirect(url_for("student_dashboard"))  # Redirect student to student dashboard
            elif user["role"] == "faculty":
                return redirect(url_for("faculty_dashboard"))  # Redirect faculty to faculty dashboard

        return jsonify({"error": "Invalid credentials!"}), 401

    return render_template("login.html")

# ---------- Student Dashboard ----------
@app.route("/student-dashboard")
def student_dashboard():
    if "user" in session and session["role"] == "student":
        return render_template("student_dashboard.html", user=session["user"])
    return redirect(url_for("login"))

# ---------- Faculty Dashboard ----------
@app.route("/faculty-dashboard")
def faculty_dashboard():
    if "user" in session and session["role"] == "faculty":
        # Fetch all OD requests from the database
        requests = list(mongo.db.requests.find({}))  # Fetch all OD requests

        # Convert ObjectId to string for rendering in HTML
        for request in requests:
            request["_id"] = str(request["_id"])

        print("Fetched OD Requests:", requests)  # Debugging line

        return render_template("faculty_dashboard.html", user=session["user"], requests=requests)

    return redirect(url_for("login"))
# ---------- Submit OD Application ----------
@app.route("/submit", methods=["POST"])
def submit_od():
    try:
        if "user" not in session or session["role"] != "student":
            return jsonify({"error": "Unauthorized!"}), 403

        # Get form data
        name = request.form.get("name")
        roll_number = request.form.get("rollNumber")
        from_date = request.form.get("fromDate")
        to_date = request.form.get("toDate")
        reason = request.form.get("reason")
        file = request.files.get("file")

        if not (name and roll_number and from_date and to_date and reason):
            return jsonify({"error": "All fields are required!"}), 400

        # Handle file upload
        file_path = None
        if file and file.filename.endswith(".pdf"):
            file_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(file_path)  # Save file locally

        # Insert into MongoDB
        od_request = {
            "student_name": name,
            "roll_number": roll_number,
            "from_date": from_date,
            "to_date": to_date,
            "reason": reason,
            "file_path": file.filename if file_path else None,  # Store only filename in DB
            "status": "Pending",  # Default status
        }
        inserted_id = mongo.db.requests.insert_one(od_request).inserted_id

        print("OD Request Added:", od_request)  # Debugging line

        return jsonify({"message": "OD application submitted!", "id": str(inserted_id)}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ---------- Approve/Reject OD Applications ----------
@app.route("/approve/<request_id>")
def approve_request(request_id):
    if "user" in session and session["role"] == "faculty":
        mongo.db.requests.update_one({"_id": ObjectId(request_id)}, {"$set": {"status": "Approved"}})
    return redirect(url_for("faculty_dashboard"))

@app.route("/reject/<request_id>")
def reject_request(request_id):
    if "user" in session and session["role"] == "faculty":
        mongo.db.requests.update_one({"_id": ObjectId(request_id)}, {"$set": {"status": "Rejected"}})
    return redirect(url_for("faculty_dashboard"))

# ---------- Fetch Approved OD Requests (Faculty) ----------
@app.route("/faculty-approved-od")
def faculty_approved_od():
    if "user" in session and session["role"] == "faculty":
        approved_requests = list(mongo.db.requests.find({"status": "Approved"}))

        # Convert ObjectId to string for rendering in HTML
        for request in approved_requests:
            request["_id"] = str(request["_id"])

        return render_template("faculty_approved_od.html", approved_requests=approved_requests)

    return redirect(url_for("login"))

# ---------- Serve Uploaded Files ----------
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ---------- Logout ----------
@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("role", None)
    return redirect(url_for("login"))

# ---------- Apply Now Route (OD Application Form) ----------
@app.route("/apply")
def apply_now():
    if "user" in session and session["role"] == "student":
        return render_template("index.html")  # Load OD Application form
    return redirect(url_for("login"))  # If not logged in, go to login page

# ---------- Approved Applications (Student) ----------
@app.route("/approved-applications")
def approved_applications():
    if "user" not in session or session["role"] != "student":
        return redirect(url_for("login"))  # Ensure only logged-in students can access

    # Fetch only approved OD applications of the logged-in student
    student_name = session["user"]
    approved_requests = list(mongo.db.requests.find({"student_name": student_name, "status": "Approved"}))

    # Convert ObjectId to string for displaying in HTML
    for request in approved_requests:
        request["_id"] = str(request["_id"])

    return render_template("approved.html", requests=approved_requests)

@app.route("/faculty-od-requests")
def faculty_od_requests():
    if "user" in session and session["role"] == "faculty":
        # Fetch all OD requests from MongoDB
        requests = list(mongo.db.requests.find())

        # Convert ObjectId to string for rendering in HTML
        for request in requests:
            request["_id"] = str(request["_id"])

        return render_template("faculty_od_requests.html", user=session["user"], requests=requests)

    return redirect(url_for("login"))

@app.route("/application-status")
def application_status():
    if "user" not in session or session["role"] != "student":
        return redirect(url_for("login"))  # Ensure only logged-in students can access

    # Fetch OD applications submitted by the logged-in student
    student_name = session["user"]
    student_requests = list(mongo.db.requests.find({"student_name": student_name}))

    # Debugging log
    print("Student's OD Requests:", student_requests)

    # Convert ObjectId to string for displaying in HTML
    for request in student_requests:
        request["_id"] = str(request["_id"])

    return render_template("application_status.html", requests=student_requests)



# ---------- Run the Flask App ----------
if __name__ == "__main__":
    app.run(debug=True)
