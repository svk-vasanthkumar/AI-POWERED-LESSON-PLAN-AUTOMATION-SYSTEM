from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_user
from app.auth.resource_access import is_manager, faculty_object_id_for_user, accessible_course_ids, ids_match
from app.database.mongodb import get_database

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_user)],
)

@router.get("/faculty-workload")
async def get_faculty_workload(current_user: dict = Depends(get_current_user)):
    db = get_database()
    
    # If faculty, only get their own data
    faculty_query = {}
    if not is_manager(current_user):
        faculty_oid = await faculty_object_id_for_user(db, current_user)
        if not faculty_oid:
            return []
        faculty_query = {"_id": faculty_oid}
        
    # Get faculty
    faculty_cursor = db.faculty.find(faculty_query)
    faculty_list = []
    async for f in faculty_cursor:
        faculty_list.append({
            "id": str(f["_id"]),
            "name": f.get("name", "Unknown"),
            "department": f.get("department", "Unknown"),
            "designation": f.get("designation", "Unknown")
        })
    
    # Get all courses to count assigned courses per faculty
    courses_cursor = db.courses.find({})
    course_counts = {}
    async for c in courses_cursor:
        fid = str(c.get("faculty_id", ""))
        if fid:
            course_counts[fid] = course_counts.get(fid, 0) + 1
            
    # Combine data
    workload = []
    for f in faculty_list:
        workload.append({
            "faculty_name": f["name"],
            "department": f["department"],
            "designation": f["designation"],
            "course_count": course_counts.get(f["id"], 0)
        })
        
    # Sort by course count descending
    workload.sort(key=lambda x: x["course_count"], reverse=True)
    return workload

@router.get("/course-progress")
async def get_course_progress(current_user: dict = Depends(get_current_user)):
    db = get_database()
    
    # Get courses (filtered by RBAC)
    courses_query = {}
    if not is_manager(current_user):
        allowed = await accessible_course_ids(db, current_user)
        if not allowed:
            return []
        variants = []
        for cid in allowed:
            variants.append(cid)
            variants.append(str(cid))
        courses_query = {"_id": {"$in": variants}}
        
    courses_cursor = db.courses.find(courses_query)
    
    progress_list = []
    async for course in courses_cursor:
        cid = course["_id"]
        cid_str = str(cid)
        
        # Check components
        has_syllabus = await db.syllabi.find_one({"course_id": {"$in": [cid, cid_str]}}) is not None
        has_timetable = await db.timetables.find_one({"course_id": {"$in": [cid, cid_str]}}) is not None
        has_lesson_plan = await db.lesson_plans.find_one({"course_id": {"$in": [cid, cid_str]}}) is not None
        
        completed = sum([has_syllabus, has_timetable, has_lesson_plan])
        percentage = round((completed / 3) * 100)
        
        status = "Not Started"
        if percentage == 100:
            status = "Ready"
        elif percentage > 0:
            status = "In Progress"
            
        progress_list.append({
            "course_name": course.get("course_name", "Unknown"),
            "course_code": course.get("course_code", "Unknown"),
            "progress_percentage": percentage,
            "status": status,
            "has_syllabus": has_syllabus,
            "has_timetable": has_timetable,
            "has_lesson_plan": has_lesson_plan
        })
        
    # Sort by progress descending
    progress_list.sort(key=lambda x: x["progress_percentage"], reverse=True)
    return progress_list


@router.get("/co-coverage")
async def get_co_coverage(current_user: dict = Depends(get_current_user)):
    db = get_database()
    
    # If faculty, only get their own courses
    query = {}
    if not is_manager(current_user):
        allowed = await accessible_course_ids(db, current_user)
        if not allowed:
            return {"department_average": 0, "course_breakdown": []}
        variants = []
        for cid in allowed:
            variants.append(cid)
            variants.append(str(cid))
        query = {"course_id": {"$in": variants}}
        
    lesson_plans_cursor = db.lesson_plans.find(query)
    
    course_coverage = []
    total_defined_cos_all = 0
    total_covered_cos_all = 0
    
    async for plan in lesson_plans_cursor:
        structured = plan.get("lesson_plan", {})
        
        # Depending on how it's stored, it might be structured_plan or lesson_plan
        if not structured and "structured_plan" in plan:
            structured = plan["structured_plan"]
            
        if not structured:
            continue
            
        course_name = structured.get("course_title", plan.get("course_name", "Unknown Course"))
        
        defined_cos = structured.get("learning_outcomes", [])
        total_defined = len(defined_cos)
        
        if total_defined == 0:
            continue
            
        # Extract covered COs from units -> topics
        covered_co_ids = set()
        units = structured.get("units", [])
        for unit in units:
            topics = unit.get("topics", [])
            for topic in topics:
                outcomes = topic.get("learning_outcomes", [])
                for outcome in outcomes:
                    covered_co_ids.add(outcome)
                    
        total_covered = len(covered_co_ids)
        
        # Calculate percentage for this course
        coverage_percentage = (total_covered / total_defined) * 100 if total_defined > 0 else 0
        
        course_coverage.append({
            "course_name": course_name,
            "total_cos": total_defined,
            "covered_cos": total_covered,
            "coverage_percentage": round(coverage_percentage, 1)
        })
        
        total_defined_cos_all += total_defined
        total_covered_cos_all += total_covered
        
    department_average = 0
    if total_defined_cos_all > 0:
        department_average = (total_covered_cos_all / total_defined_cos_all) * 100
        
    # Sort by coverage ascending to show courses needing attention first
    course_coverage.sort(key=lambda x: x["coverage_percentage"])
    
    return {
        "department_average": round(department_average, 1),
        "course_breakdown": course_coverage
    }
