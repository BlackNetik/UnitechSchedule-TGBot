# get_student_id.py

import httpx

# Cache for teachers list
_teachers_cache = None


async def get_teachers():
    """
    Fetch list of teachers from the API.
    Returns a list of teacher dictionaries with name, id, and kaf.
    """
    global _teachers_cache
    if _teachers_cache is not None:
        return _teachers_cache

    url = "https://es.unitech-mo.ru/api/raspTeacherlist"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            teachers = data.get("data", [])
            _teachers_cache = teachers
            return teachers
    except httpx.RequestError as e:
        print(f"Error fetching teachers: {e}")
        return []


async def find_teacher(search_name):
    """
    Find teacher(s) by name (partial match).
    Returns a list of matching teachers.
    """
    teachers = await get_teachers()
    if not teachers:
        return []

    search_lower = search_name.lower()
    matches = []

    for teacher in teachers:
        name = teacher.get("name", "")
        if search_lower in name.lower():
            matches.append(teacher)

    return matches


async def get_group_id(group_name):
    """
    Fetch groupID from the groups API by group name.
    """
    url = "https://es.unitech-mo.ru/api/groups"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            groups = data.get("data", {}).get("groups", [])

            for group in groups:
                if group.get("groupName").lower() == group_name.lower():
                    return group.get("groupID")

            print(f"Group '{group_name}' not found.")
            return None
    except httpx.RequestError as e:
        print(f"Error fetching groups: {e}")
        return None


async def get_first_student_id(group_id):
    """
    Fetch the first student's studentID for a given groupID.
    """
    if not group_id:
        return None

    url = f"https://es.unitech-mo.ru/api/students?groupID={group_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            students = data.get("data", {}).get("listStudents", [])

            if students:
                return students[0].get("studentID")
            else:
                print(f"No students found for groupID {group_id}.")
                return None
    except httpx.RequestError as e:
        print(f"Error fetching students: {e}")
        return None


async def get_schedule(group_name):
    """
    Get the studentID for a given group name.
    """
    group_id = await get_group_id(group_name)
    if not group_id:
        return None

    student_id = await get_first_student_id(group_id)
    if not student_id:
        return None

    return student_id
