# ============================================================
#                 HR MANAGEMENT REST API
#                 PYTHON STANDARD LIBRARY
# ============================================================

import json

import os

import re

import statistics

from datetime import datetime, date

from http.server import HTTPServer, BaseHTTPRequestHandler

from urllib.parse import urlparse, parse_qs

from email import policy

from email.parser import BytesParser

# ============================================================

# 1. PROJECT CONFIGURATION

# ============================================================

HOST = "127.0.0.1"

PORT = 8000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(DATA_DIR, exist_ok=True)

DATA_FILES = {

    "employees": "employees.json",

    "departments": "departments.json",

    "attendance": "attendance.json",

    "leaves": "leaves.json",

    "payroll": "payroll.json",

    "performance": "performance.json",

    "candidates": "candidates.json"

}

ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE"]

# ============================================================

# 2. CUSTOM API EXCEPTION

# ============================================================

class APIException(Exception):

    def __init__(self, status, message):

        self.status = status

        self.message = message

        super().__init__(message)

# ============================================================

# 3. JSON DATABASE MANAGEMENT

# ============================================================

class JSONDatabase:

    @staticmethod

    def get_path(table):

        if table not in DATA_FILES:

            raise APIException(404, "Database resource not found")

        return os.path.join(DATA_DIR, DATA_FILES[table])

    @staticmethod
    def initialize():
        """
        Create missing JSON files and repair record IDs.

        IDs are stored as integers. If older data contains numeric string IDs
        (for example "4") or duplicate IDs (4 and "4"), this method converts
        IDs to integers and assigns a new unique ID to duplicate records.
        """
        for table in DATA_FILES:
            path = JSONDatabase.get_path(table)

            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as file:
                    json.dump([], file, indent=4)

            JSONDatabase.repair_ids(table)

    @staticmethod
    def repair_ids(table):
        records = JSONDatabase.read(table)

        # Find the highest numeric ID already present in this table.
        numeric_ids = []
        for record in records:
            raw_id = record.get("id")
            if isinstance(raw_id, int) and not isinstance(raw_id, bool):
                numeric_ids.append(raw_id)
            elif isinstance(raw_id, str) and raw_id.strip().isdigit():
                numeric_ids.append(int(raw_id.strip()))

        next_available_id = max(numeric_ids, default=0) + 1
        used_ids = set()
        changed = False

        for record in records:
            raw_id = record.get("id")

            if isinstance(raw_id, int) and not isinstance(raw_id, bool):
                candidate_id = raw_id
            elif isinstance(raw_id, str) and raw_id.strip().isdigit():
                candidate_id = int(raw_id.strip())
            else:
                candidate_id = None

            # Keep the first occurrence; reassign missing or duplicate IDs.
            if candidate_id is None or candidate_id in used_ids:
                while next_available_id in used_ids or next_available_id in numeric_ids:
                    next_available_id += 1

                candidate_id = next_available_id
                next_available_id += 1

            if raw_id != candidate_id or type(raw_id) is not int:
                record["id"] = candidate_id
                changed = True

            used_ids.add(candidate_id)

        if changed:
            JSONDatabase.write(table, records)

    @staticmethod

    def read(table):

        path = JSONDatabase.get_path(table)

        try:

            with open(path, "r", encoding="utf-8") as file:

                data = json.load(file)

            if not isinstance(data, list):

                raise APIException(500, "Invalid JSON data structure")

            return data

        except json.JSONDecodeError:

            raise APIException(500, f"Invalid JSON format in {table}")

        except FileNotFoundError:

            raise APIException(404, f"{table} file not found")

    @staticmethod

    def write(table, data):

        path = JSONDatabase.get_path(table)

        temporary_path = path + ".tmp"

        try:

            with open(temporary_path, "w", encoding="utf-8") as file:

                json.dump(

                    data,

                    file,

                    indent=4,

                    ensure_ascii=False

                )

            os.replace(temporary_path, path)

        except OSError:

            if os.path.exists(temporary_path):

                os.remove(temporary_path)

            raise APIException(500, "Unable to save database records")

    @staticmethod
    def next_id(table):
        records = JSONDatabase.read(table)

        numeric_ids = []
        for record in records:
            raw_id = record.get("id")

            if isinstance(raw_id, int) and not isinstance(raw_id, bool):
                numeric_ids.append(raw_id)
            elif isinstance(raw_id, str) and raw_id.strip().isdigit():
                numeric_ids.append(int(raw_id.strip()))

        return max(numeric_ids, default=0) + 1

# ============================================================

# 4. INPUT VALIDATION

# ============================================================

class HRValidator:

    EMAIL_PATTERN = r"^[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}$"

    @staticmethod

    def required_fields(data, fields):

        if not isinstance(data, dict):

            raise APIException(400, "Request body must be a JSON object")

        for field in fields:

            if field not in data or data[field] is None:

                raise APIException(

                    400,

                    f"Missing required field: {field}"

                )

            if isinstance(data[field], str) and not data[field].strip():

                raise APIException(

                    400,

                    f"{field} cannot be empty"

                )

    @staticmethod

    def validate_email(email):

        if not isinstance(email, str) or not re.match(

            HRValidator.EMAIL_PATTERN, email

        ):

            raise APIException(400, "Invalid email address")

    @staticmethod

    def validate_phone(phone):

        if not isinstance(phone, str) or not re.fullmatch(

            r"\d{10}", phone

        ):

            raise APIException(

                400,

                "Phone number must contain exactly 10 digits"

            )

    @staticmethod

    def validate_number(value, field, minimum=0):

        if (

            isinstance(value, bool)

            or not isinstance(value, (int, float))

            or value < minimum

        ):

            raise APIException(

                400,

                f"{field} must be a number greater than or equal to {minimum}"

            )

    @staticmethod

    def validate_date(value, field):

        try:

            date.fromisoformat(value)

        except (ValueError, TypeError):

            raise APIException(

                400,

                f"{field} must use YYYY-MM-DD format"

            )

    @staticmethod

    def validate_status(value, allowed, field="status"):

        if value not in allowed:

            raise APIException(

                400,

                f"Invalid {field}. Allowed values: {', '.join(allowed)}"

            )

# ============================================================

# 5. GENERIC RECORD MANAGEMENT

# ============================================================

class RecordService:

    @staticmethod

    def get_all(table):

        return JSONDatabase.read(table)

    @staticmethod

    def get_by_id(table, record_id):

        records = JSONDatabase.read(table)

        for record in records:

            if str(record.get("id")) == str(record_id):

                return record

        raise APIException(404, f"{table} record not found")

    @staticmethod

    def create(table, data):

        records = JSONDatabase.read(table)

        record = data.copy()

        record["id"] = JSONDatabase.next_id(table)

        records.append(record)

        JSONDatabase.write(table, records)

        return record

    @staticmethod
    def update(table, record_id, data):
        records = JSONDatabase.read(table)

        for record in records:
            if str(record.get("id")) == str(record_id):
                # Preserve the original ID and its integer data type.
                original_id = record["id"]

                # Prevent clients from changing a record's ID in the body.
                safe_data = data.copy()
                safe_data.pop("id", None)

                record.update(safe_data)
                record["id"] = original_id

                JSONDatabase.write(table, records)
                return record

        raise APIException(404, f"{table} record not found")

    @staticmethod

    def delete(table, record_id):

        records = JSONDatabase.read(table)

        updated = [

            record for record in records

            if str(record.get("id")) != str(record_id)

        ]

        if len(updated) == len(records):

            raise APIException(404, f"{table} record not found")

        JSONDatabase.write(table, updated)

        return {"message": f"{table} record deleted successfully"}

# ============================================================

# 6. EMPLOYEE MANAGEMENT

# ============================================================

class EmployeeService:

    REQUIRED = [

        "name",

        "age",

        "email",

        "phone",

        "department",

        "designation",

        "salary",

        "joining_date"

    ]

    ALLOWED = REQUIRED + ["status"]

    @staticmethod

    def get_all():

        return JSONDatabase.read("employees")

    @staticmethod

    def get_by_id(employee_id):

        return RecordService.get_by_id("employees", employee_id)

    @staticmethod

    def search(keyword):

        employees = EmployeeService.get_all()

        keyword = keyword.lower()

        return [

            employee for employee in employees

            if keyword in str(employee.get("name", "")).lower()

            or keyword in str(employee.get("department", "")).lower()

            or keyword in str(employee.get("designation", "")).lower()

        ]

    @staticmethod

    def create(data):

        HRValidator.required_fields(data, EmployeeService.REQUIRED)

        EmployeeService.validate_data(data)

        employees = EmployeeService.get_all()

        email = data["email"].lower()

        if any(

            employee.get("email", "").lower() == email

            for employee in employees

        ):

            raise APIException(409, "Employee email already exists")

        record = {

            "name": data["name"].strip(),

            "age": data["age"],

            "email": email,

            "phone": data["phone"],

            "department": data["department"].strip(),

            "designation": data["designation"].strip(),

            "salary": data["salary"],

            "joining_date": data["joining_date"],

            "status": data.get("status", "Active")

        }

        if record["status"] not in ["Active", "Inactive"]:

            raise APIException(400, "Invalid employee status")

        return RecordService.create("employees", record)

    @staticmethod

    def validate_data(data):

        if "email" in data:

            HRValidator.validate_email(data["email"])

        if "phone" in data:

            HRValidator.validate_phone(data["phone"])

        if "age" in data:

            HRValidator.validate_number(data["age"], "Age", 18)

        if "salary" in data:

            HRValidator.validate_number(data["salary"], "Salary")

        if "joining_date" in data:

            HRValidator.validate_date(data["joining_date"], "Joining date")

    @staticmethod

    def update(employee_id, data):

        if not isinstance(data, dict) or not data:

            raise APIException(400, "Update data cannot be empty")

        unknown = set(data) - set(EmployeeService.ALLOWED)

        if unknown:

            raise APIException(

                400,

                f"Invalid employee fields: {', '.join(sorted(unknown))}"

            )

        employees = EmployeeService.get_all()

        current = next(

            (

                employee for employee in employees

                if str(employee["id"]) == str(employee_id)

            ),

            None

        )

        if current is None:

            raise APIException(404, "Employee not found")

        EmployeeService.validate_data(data)

        if "email" in data:

            email = data["email"].lower()

            if any(

                employee.get("email", "").lower() == email

                and str(employee["id"]) != str(employee_id)

                for employee in employees

            ):

                raise APIException(409, "Email already belongs to another employee")

            data["email"] = email

        if "status" in data:

            HRValidator.validate_status(

                data["status"],

                ["Active", "Inactive"],

                "employee status"

            )

        return RecordService.update("employees", employee_id, data)

    @staticmethod

    def delete(employee_id):

        # Preserve historical records by not cascading deletion.

        return RecordService.delete("employees", employee_id)

# ============================================================

# 7. DEPARTMENT MANAGEMENT

# ============================================================

class DepartmentService:

    @staticmethod

    def get_all():

        return JSONDatabase.read("departments")

    @staticmethod

    def create(data):

        HRValidator.required_fields(data, ["name", "manager", "location"])

        departments = DepartmentService.get_all()

        if any(

            d["name"].lower() == data["name"].strip().lower()

            for d in departments

        ):

            raise APIException(409, "Department already exists")

        department = {

            "name": data["name"].strip(),

            "manager": data["manager"].strip(),

            "location": data["location"].strip()

        }

        return RecordService.create("departments", department)

    @staticmethod

    def update(department_id, data):

        allowed = {"name", "manager", "location"}

        if not isinstance(data, dict) or not data:

            raise APIException(400, "Update data cannot be empty")

        if set(data) - allowed:

            raise APIException(400, "Invalid department fields")

        DepartmentService.get_all()

        if "name" in data:

            for department in DepartmentService.get_all():

                if (

                    department["name"].lower() == data["name"].strip().lower()

                    and str(department["id"]) != str(department_id)

                ):

                    raise APIException(409, "Department name already exists")

        return RecordService.update("departments", department_id, data)

    @staticmethod

    def delete(department_id):

        employees = EmployeeService.get_all()

        department = RecordService.get_by_id(

            "departments", department_id

        )

        if any(

            employee.get("department", "").lower()

            == department["name"].lower()

            for employee in employees

        ):

            raise APIException(

                409,

                "Cannot delete department while employees are assigned to it"

            )

        return RecordService.delete("departments", department_id)

# ============================================================

# 8. ATTENDANCE MANAGEMENT

# ============================================================

class AttendanceService:

    @staticmethod

    def get_all():

        return JSONDatabase.read("attendance")

    @staticmethod

    def get_employee_attendance(employee_id):

        EmployeeService.get_by_id(employee_id)

        records = AttendanceService.get_all()

        return [

            record for record in records

            if str(record["employee_id"]) == str(employee_id)

        ]

    @staticmethod

    def check_in(data):

        HRValidator.required_fields(data, ["employee_id"])

        employee = EmployeeService.get_by_id(data["employee_id"])

        if employee.get("status") != "Active":

            raise APIException(409, "Inactive employee cannot mark attendance")

        records = AttendanceService.get_all()

        today = date.today().isoformat()

        existing = [

            record for record in records

            if str(record["employee_id"]) == str(data["employee_id"])

            and record["date"] == today

        ]

        if existing:

            raise APIException(409, "Attendance already marked today")

        record = {

            "employee_id": data["employee_id"],

            "employee_name": employee["name"],

            "date": today,

            "check_in": datetime.now().strftime("%H:%M:%S"),

            "check_out": None,

            "working_hours": 0,

            "status": "Present"

        }

        return RecordService.create("attendance", record)

    @staticmethod

    def check_out(data):

        HRValidator.required_fields(data, ["employee_id"])

        records = AttendanceService.get_all()

        today = date.today().isoformat()

        for record in records:

            if (

                str(record["employee_id"]) == str(data["employee_id"])

                and record["date"] == today

            ):

                if record.get("check_in") is None:

                    raise APIException(409, "Check-in record is missing")

                if record.get("check_out") is not None:

                    raise APIException(409, "Employee already checked out")

                check_in = datetime.strptime(

                    record["check_in"], "%H:%M:%S"

                )

                check_out = datetime.now()

                hours = (

                    check_out - check_in.replace(

                        year=check_out.year,

                        month=check_out.month,

                        day=check_out.day

                    )

                ).total_seconds() / 3600

                record["check_out"] = check_out.strftime("%H:%M:%S")

                record["working_hours"] = round(max(0, hours), 2)

                JSONDatabase.write("attendance", records)

                return record

        raise APIException(404, "Today's attendance record not found")

    @staticmethod

    def monthly_summary(employee_id):

        records = AttendanceService.get_employee_attendance(employee_id)

        present = sum(

            1 for r in records if r.get("status") == "Present"

        )

        absent = sum(

            1 for r in records if r.get("status") == "Absent"

        )

        return {

            "employee_id": employee_id,

            "total_records": len(records),

            "present_days": present,

            "absent_days": absent

        }

# ============================================================

# 9. LEAVE MANAGEMENT

# ============================================================

class LeaveService:

    ALLOWED_TYPES = [

        "Sick Leave",

        "Casual Leave",

        "Earned Leave",

        "Maternity Leave",

        "Paternity Leave",

        "Unpaid Leave"

    ]

    @staticmethod

    def get_all():

        return JSONDatabase.read("leaves")

    @staticmethod

    def apply(data):

        HRValidator.required_fields(

            data,

            ["employee_id", "leave_type",

             "from_date", "to_date", "reason"]

        )

        EmployeeService.get_by_id(data["employee_id"])

        HRValidator.validate_status(

            data["leave_type"],

            LeaveService.ALLOWED_TYPES,

            "leave type"

        )

        HRValidator.validate_date(data["from_date"], "From date")

        HRValidator.validate_date(data["to_date"], "To date")

        start = date.fromisoformat(data["from_date"])

        end = date.fromisoformat(data["to_date"])

        if end < start:

            raise APIException(400, "To date cannot be before from date")

        if start < date.today():

            raise APIException(400, "Leave cannot start in the past")

        leaves = LeaveService.get_all()

        for leave in leaves:

            if (

                str(leave["employee_id"]) == str(data["employee_id"])

                and leave["status"] in ["Pending", "Approved"]

            ):

                old_start = date.fromisoformat(leave["from_date"])

                old_end = date.fromisoformat(leave["to_date"])

                if start <= old_end and end >= old_start:

                    raise APIException(

                        409,

                        "Leave dates overlap with an existing request"

                    )

        total_days = (end - start).days + 1

        employee = EmployeeService.get_by_id(data["employee_id"])

        record = {

            "employee_id": data["employee_id"],

            "employee_name": employee["name"],

            "leave_type": data["leave_type"],

            "from_date": data["from_date"],

            "to_date": data["to_date"],

            "total_days": total_days,

            "reason": data["reason"],

            "status": "Pending",

            "applied_on": date.today().isoformat()

        }

        return RecordService.create("leaves", record)

    @staticmethod

    def update_status(leave_id, data):

        HRValidator.required_fields(data, ["status"])

        HRValidator.validate_status(

            data["status"],

            ["Approved", "Rejected"],

            "leave status"

        )

        leave = RecordService.get_by_id("leaves", leave_id)

        if leave["status"] != "Pending":

            raise APIException(409, "Leave request already processed")

        return RecordService.update(

            "leaves",

            leave_id,

            {"status": data["status"]}

        )

    @staticmethod

    def cancel(leave_id):

        leave = RecordService.get_by_id("leaves", leave_id)

        if leave["status"] != "Pending":

            raise APIException(409, "Only pending leave can be cancelled")

        return RecordService.update(

            "leaves",

            leave_id,

            {"status": "Cancelled"}

        )

# ============================================================

# 10. PAYROLL MANAGEMENT

# ============================================================

class PayrollService:

    @staticmethod

    def get_all():

        return JSONDatabase.read("payroll")

    @staticmethod

    def calculate(data):

        HRValidator.required_fields(

            data,

            ["employee_id", "month", "year",

             "basic_salary", "allowance", "bonus", "deduction"]

        )

        employee = EmployeeService.get_by_id(data["employee_id"])

        month = data["month"]

        if not isinstance(month, str) or not month.strip():

            raise APIException(400, "Month is required")

        HRValidator.validate_number(data["year"], "Year", 2000)

        if data["year"] > 2100:

            raise APIException(400, "Invalid payroll year")

        for field in [

            "basic_salary", "allowance", "bonus", "deduction"

        ]:

            HRValidator.validate_number(data[field], field)

        basic = float(data["basic_salary"])

        allowance = float(data["allowance"])

        bonus = float(data["bonus"])

        deduction = float(data["deduction"])

        gross = basic + allowance + bonus

        net = gross - deduction

        if net < 0:

            raise APIException(400, "Deductions exceed gross salary")

        payroll_records = PayrollService.get_all()

        if any(

            str(p["employee_id"]) == str(data["employee_id"])

            and p["month"].lower() == month.lower()

            and p["year"] == data["year"]

            for p in payroll_records

        ):

            raise APIException(

                409,

                "Payroll already exists for this employee and month"

            )

        record = {

            "employee_id": data["employee_id"],

            "employee_name": employee["name"],

            "month": month,

            "year": data["year"],

            "basic_salary": basic,

            "allowance": allowance,

            "bonus": bonus,

            "deduction": deduction,

            "gross_salary": round(gross, 2),

            "net_salary": round(net, 2),

            "payment_status": "Pending",

            "processed_date": date.today().isoformat()

        }

        return RecordService.create("payroll", record)

    @staticmethod

    def update_payment(payroll_id, data):

        HRValidator.required_fields(data, ["payment_status"])

        HRValidator.validate_status(

            data["payment_status"],

            ["Paid", "Pending"],

            "payment status"

        )

        return RecordService.update(

            "payroll",

            payroll_id,

            {"payment_status": data["payment_status"]}

        )

    @staticmethod

    def employee_payroll(employee_id):

        EmployeeService.get_by_id(employee_id)

        records = PayrollService.get_all()

        return [

            p for p in records

            if str(p["employee_id"]) == str(employee_id)

        ]

# ============================================================

# 11. PERFORMANCE MANAGEMENT

# ============================================================

class PerformanceService:

    @staticmethod

    def get_all():

        return JSONDatabase.read("performance")

    @staticmethod

    def add_review(data):

        HRValidator.required_fields(

            data,

            ["employee_id", "review_period",

             "rating", "feedback", "reviewed_by"]

        )

        employee = EmployeeService.get_by_id(data["employee_id"])

        HRValidator.validate_number(

            data["rating"], "Rating", 1

        )

        if data["rating"] > 5:

            raise APIException(400, "Rating cannot exceed 5")

        record = {

            "employee_id": data["employee_id"],

            "employee_name": employee["name"],

            "review_period": data["review_period"],

            "rating": data["rating"],

            "feedback": data["feedback"],

            "reviewed_by": data["reviewed_by"],

            "review_date": date.today().isoformat()

        }

        return RecordService.create("performance", record)

    @staticmethod

    def employee_reviews(employee_id):

        EmployeeService.get_by_id(employee_id)

        return [

            review for review in PerformanceService.get_all()

            if str(review["employee_id"]) == str(employee_id)

        ]

    @staticmethod

    def average_rating():

        reviews = PerformanceService.get_all()

        ratings = [

            review["rating"]

            for review in reviews

            if isinstance(review.get("rating"), (int, float))

            and not isinstance(review.get("rating"), bool)

        ]

        return {

            "total_reviews": len(ratings),

            "average_rating": (

                round(statistics.mean(ratings), 2)

                if ratings else 0

            )

        }

# ============================================================

# 12. RECRUITMENT MANAGEMENT

# ============================================================

class RecruitmentService:

    STATUSES = [

        "Applied",

        "Interview Scheduled",

        "Selected",

        "Rejected",

        "On Hold"

    ]

    @staticmethod

    def get_all():

        return JSONDatabase.read("candidates")

    @staticmethod

    def add_candidate(data):

        HRValidator.required_fields(

            data,

            ["name", "email", "phone",

             "position", "experience", "qualification"]

        )

        HRValidator.validate_email(data["email"])

        HRValidator.validate_phone(data["phone"])

        HRValidator.validate_number(

            data["experience"], "Experience"

        )

        candidates = RecruitmentService.get_all()

        if any(

            c["email"].lower() == data["email"].lower()

            for c in candidates

        ):

            raise APIException(409, "Candidate email already exists")

        record = {

            "name": data["name"].strip(),

            "email": data["email"].lower(),

            "phone": data["phone"],

            "position": data["position"],

            "experience": data["experience"],

            "qualification": data["qualification"],

            "interview_status": "Applied",

            "application_date": date.today().isoformat()

        }

        return RecordService.create("candidates", record)

    @staticmethod

    def update_status(candidate_id, data):

        HRValidator.required_fields(data, ["interview_status"])

        HRValidator.validate_status(

            data["interview_status"],

            RecruitmentService.STATUSES,

            "interview status"

        )

        return RecordService.update(

            "candidates",

            candidate_id,

            {"interview_status": data["interview_status"]}

        )

# ============================================================

# 13. HR REPORTS AND ANALYTICS

# ============================================================

class HRReportService:

    @staticmethod

    def dashboard():

        employees = EmployeeService.get_all()

        departments = JSONDatabase.read("departments")

        attendance = AttendanceService.get_all()

        leaves = LeaveService.get_all()

        payroll = PayrollService.get_all()

        performance = PerformanceService.get_all()

        candidates = RecruitmentService.get_all()

        active_employees = [

            e for e in employees

            if e.get("status") == "Active"

        ]

        salaries = [

            float(e["salary"])

            for e in employees

            if isinstance(e.get("salary"), (int, float))

            and not isinstance(e.get("salary"), bool)

        ]

        department_summary = {}

        for employee in employees:

            department = employee.get("department", "Unknown")

            department_summary[department] = (

                department_summary.get(department, 0) + 1

            )

        leave_summary = {}

        for leave in leaves:

            status = leave.get("status", "Unknown")

            leave_summary[status] = (

                leave_summary.get(status, 0) + 1

            )

        payroll_total = sum(

            p.get("net_salary", 0)

            for p in payroll

            if isinstance(p.get("net_salary"), (int, float))

        )

        return {

            "generated_at": datetime.now().isoformat(),

            "employee_statistics": {

                "total_employees": len(employees),

                "active_employees": len(active_employees),

                "inactive_employees": len(employees) - len(active_employees)

            },

            "department_statistics": {

                "total_departments": len(departments),

                "employee_distribution": department_summary

            },

            "attendance_statistics": {

                "total_attendance_records": len(attendance)

            },

            "leave_statistics": leave_summary,

            "payroll_statistics": {

                "total_payroll_records": len(payroll),

                "total_net_salary": round(payroll_total, 2),

                "average_employee_salary": (

                    round(statistics.mean(salaries), 2)

                    if salaries else 0

                )

            },

            "performance_statistics": {

                "total_reviews": len(performance),

                "average_rating": (

                    round(

                        statistics.mean([

                            p["rating"] for p in performance

                            if isinstance(p.get("rating"), (int, float))

                            and not isinstance(p.get("rating"), bool)

                        ]),

                        2

                    )

                    if any(

                        isinstance(p.get("rating"), (int, float))

                        and not isinstance(p.get("rating"), bool)

                        for p in performance

                    )

                    else 0

                )

            },

            "recruitment_statistics": {

                "total_candidates": len(candidates),

                "selected": sum(

                    1 for c in candidates

                    if c.get("interview_status") == "Selected"

                ),

                "rejected": sum(

                    1 for c in candidates

                    if c.get("interview_status") == "Rejected"

                )

            }

        }

    @staticmethod

    def department_report():

        employees = EmployeeService.get_all()

        result = {}

        for employee in employees:

            department = employee.get("department", "Unknown")

            if department not in result:

                result[department] = {

                    "employee_count": 0,

                    "total_salary": 0

                }

            result[department]["employee_count"] += 1

            result[department]["total_salary"] += employee.get("salary", 0)

        for department in result:

            count = result[department]["employee_count"]

            result[department]["average_salary"] = round(

                result[department]["total_salary"] / count,

                2

            ) if count else 0

        return result

# ============================================================

# 14. API REQUEST HANDLER

# ============================================================

class HRRequestHandler(BaseHTTPRequestHandler):

    server_version = "HRManagementAPI/1.0"

    def log_message(self, format, *args):

        print(

            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "

            f"{self.client_address[0]} - {format % args}"

        )

    # --------------------------------------------------------

    # RESPONSE HANDLER

    # --------------------------------------------------------

    def send_json(self, status, data):

        response = json.dumps(

            data,

            indent=4,

            ensure_ascii=False

        ).encode("utf-8")

        self.send_response(status)

        self.send_header(

            "Content-Type",

            "application/json; charset=utf-8"

        )

        self.send_header(

            "Content-Length",

            str(len(response))

        )

        self.send_header("Cache-Control", "no-store")

        self.send_header("Access-Control-Allow-Origin", "*")

        self.send_header(

            "Access-Control-Allow-Methods",

            "GET, POST, PUT, DELETE, OPTIONS"

        )

        self.send_header(

            "Access-Control-Allow-Headers",

            "Content-Type"

        )

        self.end_headers()

        self.wfile.write(response)

    # --------------------------------------------------------

    # REQUEST BODY READER

    # --------------------------------------------------------

    def read_body(self):

        try:

            content_length = int(

                self.headers.get("Content-Length", 0)

            )

        except ValueError:

            raise APIException(400, "Invalid Content-Length")

        if content_length <= 0:

            raise APIException(400, "Request body is required")

        if content_length > 1024 * 1024:

            raise APIException(413, "Request body is too large")

        content_type = self.headers.get(

            "Content-Type", ""

        ).split(";")[0].strip().lower()

        if content_type != "application/json":

            raise APIException(

                415,

                "Content-Type must be application/json"

            )

        raw_data = self.rfile.read(content_length)

        try:

            data = json.loads(raw_data.decode("utf-8"))

        except (json.JSONDecodeError, UnicodeDecodeError):

            raise APIException(400, "Invalid JSON request body")

        if not isinstance(data, dict):

            raise APIException(400, "JSON body must be an object")

        return data

    # --------------------------------------------------------

    # URL PARSER

    # --------------------------------------------------------

    def get_request_path(self):

        parsed = urlparse(self.path)

        path_parts = [

            part for part in parsed.path.strip("/").split("/")

            if part

        ]

        query_params = parse_qs(parsed.query)

        return path_parts, query_params

    # --------------------------------------------------------

    # CENTRALIZED ERROR HANDLING

    # --------------------------------------------------------

    def handle_request(self, function):

        try:

            result = function()

            if isinstance(result, tuple):

                status, data = result

            else:

                status, data = 200, result

            self.send_json(status, {

                "success": True,

                "data": data

            })

        except APIException as error:

            self.send_json(error.status, {

                "success": False,

                "error": error.message

            })

        except (KeyError, TypeError, ValueError) as error:

            self.send_json(400, {

                "success": False,

                "error": f"Invalid request data: {error}"

            })

        except Exception as error:

            print("Internal API error:", repr(error))

            self.send_json(500, {

                "success": False,

                "error": "Internal server error"

            })

    # --------------------------------------------------------

    # HOME AND API INFORMATION

    # --------------------------------------------------------

    def home(self):

        return {

            "project": "HR Management REST API",

            "version": "1.0",

            "technology": "Python Standard Library",

            "description": "Human Resource Management System",

            "available_methods": ALLOWED_METHODS,

            "modules": list(DATA_FILES.keys()),

            "message": "HR REST API is running successfully"

        }

    # --------------------------------------------------------

    # GET ROUTES

    # --------------------------------------------------------

    def do_GET(self):

        self.handle_request(self.route_get)

    def route_get(self):

        parts, query = self.get_request_path()

        if not parts:

            return self.home()

        if parts == ["health"]:

            return {

                "status": "Healthy",

                "server_time": datetime.now().isoformat()

            }

        if parts == ["employees"]:

            employees = EmployeeService.get_all()

            keyword = query.get("search", [None])[0]

            if keyword:

                employees = EmployeeService.search(keyword)

            department = query.get("department", [None])[0]

            if department:

                employees = [

                    e for e in employees

                    if e.get("department", "").lower()

                    == department.lower()

                ]

            status = query.get("status", [None])[0]

            if status:

                employees = [

                    e for e in employees

                    if e.get("status", "").lower() == status.lower()

                ]

            return employees

        if len(parts) == 2 and parts[0] == "employees":

            return EmployeeService.get_by_id(parts[1])

        if parts == ["departments"]:

            return DepartmentService.get_all()

        if len(parts) == 2 and parts[0] == "departments":

            return RecordService.get_by_id("departments", parts[1])

        if parts == ["attendance"]:

            return AttendanceService.get_all()

        if len(parts) == 3 and parts[0] == "attendance" and parts[1] == "employee":

            return AttendanceService.get_employee_attendance(parts[2])

        if (
            len(parts) == 4
            and parts[0] == "attendance"
            and parts[1] == "summary"
            and parts[3] == "monthly"
        ):
            return AttendanceService.monthly_summary(parts[2])

        if parts == ["leaves"]:

            return LeaveService.get_all()

        if parts == ["leaves", "pending"]:

            return [

                leave for leave in LeaveService.get_all()

                if leave.get("status") == "Pending"

            ]

        if len(parts) == 2 and parts[0] == "leaves":

            return RecordService.get_by_id("leaves", parts[1])

        if parts == ["payroll"]:

            return PayrollService.get_all()

        if len(parts) == 3 and parts[0] == "payroll" and parts[1] == "employee":

            return PayrollService.employee_payroll(parts[2])

        if parts == ["performance"]:

            return PerformanceService.get_all()

        if len(parts) == 3 and parts[0] == "performance" and parts[1] == "employee":

            return PerformanceService.employee_reviews(parts[2])

        if parts == ["candidates"]:

            return RecruitmentService.get_all()

        if len(parts) == 2 and parts[0] == "candidates":

            return RecordService.get_by_id("candidates", parts[1])

        if parts == ["reports", "dashboard"]:

            return HRReportService.dashboard()

        if parts == ["reports", "departments"]:

            return HRReportService.department_report()

        if parts == ["reports", "performance"]:

            return PerformanceService.average_rating()

        raise APIException(404, "GET endpoint not found")

    # --------------------------------------------------------

    # POST ROUTES

    # --------------------------------------------------------

    def do_POST(self):

        self.handle_request(self.route_post)

    def route_post(self):

        parts, query = self.get_request_path()

        data = self.read_body()

        if parts == ["employees"]:

            return 201, EmployeeService.create(data)

        if parts == ["departments"]:

            return 201, DepartmentService.create(data)

        if parts == ["attendance", "check-in"]:

            return 201, AttendanceService.check_in(data)

        if parts == ["attendance", "check-out"]:

            return AttendanceService.check_out(data)

        if parts == ["leaves"]:

            return 201, LeaveService.apply(data)

        if len(parts) == 3 and parts[0] == "leaves" and parts[2] == "decision":

            return LeaveService.update_status(parts[1], data)

        if parts == ["payroll", "calculate"]:

            return 201, PayrollService.calculate(data)

        if parts == ["performance"]:

            return 201, PerformanceService.add_review(data)

        if parts == ["candidates"]:

            return 201, RecruitmentService.add_candidate(data)

        if (

            len(parts) == 3

            and parts[0] == "candidates"

            and parts[2] == "status"

        ):

            return RecruitmentService.update_status(parts[1], data)

        raise APIException(404, "POST endpoint not found")

    # --------------------------------------------------------

    # PUT ROUTES

    # --------------------------------------------------------

    def do_PUT(self):

        self.handle_request(self.route_put)

    def route_put(self):

        parts, query = self.get_request_path()

        data = self.read_body()

        if len(parts) == 2 and parts[0] == "employees":

            return EmployeeService.update(parts[1], data)

        if len(parts) == 2 and parts[0] == "departments":

            return DepartmentService.update(parts[1], data)

        if len(parts) == 2 and parts[0] == "leaves":

            return LeaveService.update_status(parts[1], data)

        if len(parts) == 2 and parts[0] == "payroll":

            return PayrollService.update_payment(parts[1], data)

        if (

            len(parts) == 2

            and parts[0] == "candidates"

        ):

            return RecruitmentService.update_status(parts[1], data)

        raise APIException(404, "PUT endpoint not found")

    # --------------------------------------------------------

    # DELETE ROUTES

    # --------------------------------------------------------

    def do_DELETE(self):

        self.handle_request(self.route_delete)

    def route_delete(self):

        parts, query = self.get_request_path()

        if len(parts) == 2 and parts[0] == "employees":

            return EmployeeService.delete(parts[1])

        if len(parts) == 2 and parts[0] == "departments":

            return DepartmentService.delete(parts[1])

        if len(parts) == 2 and parts[0] == "leaves":

            return LeaveService.cancel(parts[1])

        if len(parts) == 2 and parts[0] == "candidates":

            return RecordService.delete("candidates", parts[1])

        raise APIException(404, "DELETE endpoint not found")

    # --------------------------------------------------------

    # OPTIONS REQUEST

    # --------------------------------------------------------

    def do_OPTIONS(self):

        self.send_response(204)

        self.send_header(

            "Access-Control-Allow-Origin", "*"

        )

        self.send_header(

            "Access-Control-Allow-Methods",

            "GET, POST, PUT, DELETE, OPTIONS"

        )

        self.send_header(

            "Access-Control-Allow-Headers",

            "Content-Type"

        )

        self.send_header("Content-Length", "0")

        self.end_headers()

    # --------------------------------------------------------

    # METHOD NOT ALLOWED

    # --------------------------------------------------------

    def do_PATCH(self):

        self.send_json(405, {

            "success": False,

            "error": "PATCH method is not supported"

        })

# ============================================================

# 15. START THE HR REST API SERVER

# ============================================================

def start_server():

    JSONDatabase.initialize()

    server_address = (HOST, PORT)

    server = HTTPServer(

        server_address,

        HRRequestHandler

    )

    print("=" * 60)

    print("             HR MANAGEMENT REST API")

    print("=" * 60)

    print(f"Server Address : http://{HOST}:{PORT}")

    print(f"API Home       : http://{HOST}:{PORT}/")

    print(f"Health Check   : http://{HOST}:{PORT}/health")

    print("-" * 60)

    print("Available Modules:")

    for module in DATA_FILES:

        print(f"  - {module.title()}")

    print("-" * 60)

    print("Supported HTTP Methods:")

    for method in ALLOWED_METHODS:

        print(f"  - {method}")

    print("=" * 60)

    print("HR REST API is ready to accept requests...")

    print("Press CTRL + C to stop the server.")

    try:

        server.serve_forever()

    except KeyboardInterrupt:

        print("\nShutting down HR REST API...")

        server.server_close()

        print("Server stopped successfully.")

# ============================================================

# 16. APPLICATION ENTRY POINT

# ============================================================

if __name__ == "__main__":

    start_server()