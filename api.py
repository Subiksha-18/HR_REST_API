
from fastapi import FastAPI, HTTPException, Body
import main

app = FastAPI(
    title="HR Management REST API",
    description="Employee, Department, Attendance, Leave, Payroll, Performance and Recruitment API",
    version="1.0.0"
)

# Initialize existing JSON database
main.JSONDatabase.initialize()


# --------------------------------------------------
# SERVICE CONFIGURATION
# --------------------------------------------------

MODULES = {
    "employees": main.EmployeeService,
    "departments": main.DepartmentService,
    "attendance": main.AttendanceService,
    "leaves": main.LeaveService,
    "payroll": main.PayrollService,
    "performance": main.PerformanceService,
    "candidates": main.RecruitmentService
}


def call_service(service, possible_methods, *args):
    """Call the first supported method from a service."""
    for method_name in possible_methods:
        method = getattr(service, method_name, None)

        if callable(method):
            return method(*args)

    raise HTTPException(
        status_code=501,
        detail=(
            f"No compatible method found in {service.__name__}. "
            f"Expected one of: {possible_methods}"
        )
    )


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "success": True,
        "message": "HR Management REST API is running",
        "modules": list(MODULES.keys())
    }


@app.get("/health")
def health():
    return {
        "success": True,
        "message": "API is healthy"
    }


# --------------------------------------------------
# GENERIC CRUD ROUTES
# --------------------------------------------------

def get_all_records(module):
    service = MODULES[module]

    data = call_service(
        service,
        ["get_all", "get_all_records", "list_all"]
    )

    return {"success": True, "data": data}


def get_record(module, record_id):
    service = MODULES[module]

    data = call_service(
        service,
        ["get_by_id", "get_record_by_id", "get_one"],
        record_id
    )

    if data is None:
        raise HTTPException(status_code=404, detail="Record not found")

    return {"success": True, "data": data}


def create_record(module, record):
    service = MODULES[module]

    data = call_service(
        service,
        ["create", "add", "create_record", "add_record"],
        record
    )

    return {"success": True, "data": data}


def update_record(module, record_id, record):
    service = MODULES[module]

    data = call_service(
        service,
        ["update", "update_record", "edit"],
        record_id,
        record
    )

    if data is None:
        raise HTTPException(status_code=404, detail="Record not found")

    return {"success": True, "data": data}


def delete_record(module, record_id):
    service = MODULES[module]

    data = call_service(
        service,
        ["delete", "delete_record", "remove"],
        record_id
    )

    if data is False or data is None:
        raise HTTPException(status_code=404, detail="Record not found")

    return {"success": True, "data": data}


# --------------------------------------------------
# REGISTER ROUTES FOR ALL MODULES
# --------------------------------------------------

for module_name in MODULES:

    @app.get(f"/{module_name}", name=f"get_{module_name}")
    def get_all(module=module_name):
        return get_all_records(module)

    @app.get(f"/{module_name}/{{record_id}}", name=f"get_{module_name}_by_id")
    def get_one(record_id: int, module=module_name):
        return get_record(module, record_id)

    @app.post(f"/{module_name}", name=f"create_{module_name}")
    def create_one(record: dict = Body(...), module=module_name):
        return create_record(module, record)

    @app.put(f"/{module_name}/{{record_id}}", name=f"update_{module_name}")
    def update_one(
        record_id: int,
        record: dict = Body(...),
        module=module_name
    ):
        return update_record(module, record_id, record)

    @app.delete(f"/{module_name}/{{record_id}}", name=f"delete_{module_name}")
    def delete_one(record_id: int, module=module_name):
        return delete_record(module, record_id)


# --------------------------------------------------
# STARTUP MESSAGE
# --------------------------------------------------

@app.get("/api-info")
def api_info():
    return {
        "success": True,
        "message": "HR Management API",
        "available_modules": list(MODULES.keys()),
        "documentation": "/docs"
    }
