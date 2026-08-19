from app.services.academic_calendar_parser import parse_academic_calendar_text


def test_parse_real_college_calendar_shape():
    raw = '''
    Adhiyamaan College of Engineering (An Autonomous Institution)
    Academic Schedule (UG&PG) III, IV year B.E/B.Tech 2026-2027 (ODD Semester)
    Commencement of V, VII & IX (Arch) Semester Classes 01.07.2026
    July 27 August 24 September 24 October 21 November 11
    Continuous Internal Assessment-I 25.07.2026 to 10.08.2026
    Continuous Internal Assessment-II 22.08.2026 to 07.09.2026
    Continuous Internal Assessment-III 19.09.2026 to 05.10.2026
    Model practical Examination 12.10.2026 to 14.10.2026
    Remedial / Revision Classes 15.10.2026 to 17.10.2026
    Model Theory Examination 22.10.2026 to 28.10.2026
    Last Working Day 28.10.2026
    Semester End Practical Examinations 30.10.2026 to 07.11.2026
    Semester End Theory Examinations 16.11.2026 to 23.12.2026
    Winter Vacation 24.12.2026 to 03.01.2027
    15.08.2026 - Independence Day
    26.08.2026 - Milad-un-Nabi
    04.09.2026 - Krishna Jayanthi
    14.09.2026 - Vinayakar Chathurthi
    17.08.2026 - Thursday Timetable
    12.09.2026 - Friday Timetable
    Total No. of Working Days 96
    '''
    calendar = parse_academic_calendar_text(
        raw,
        original_filename="Academic Schedule 2026-2027.pdf",
        extraction_method="text",
    )
    assert calendar.academic_year == "2026-2027"
    assert calendar.semester == 7
    assert calendar.semester_start.isoformat() == "2026-07-01"
    assert calendar.semester_end.isoformat() == "2026-12-23"
    assert calendar.total_working_days == 96
    assert any(h.name == "Independence Day" for h in calendar.holidays)
    assert any(s.timetable_day == "Thursday" for s in calendar.special_days)
    assert any(e.type == "semester_end_theory" for e in calendar.events)
