from fastapi import APIRouter, Depends

from app.utils.auth import get_current_user, require_roles


router = APIRouter(
    prefix="/test-auth",
    tags=["Authorization Test"],
)


@router.get("/any")
async def any_authenticated_user(
    current_user=Depends(get_current_user),
):
    return {
        "message": "Authenticated",
        "role": current_user["role"],
    }


@router.get("/faculty")
async def faculty_only(
    current_user=Depends(
        require_roles("faculty")
    ),
):
    return {
        "message": "Faculty access granted",
        "role": current_user["role"],
    }


@router.get("/management")
async def management_only(
    current_user=Depends(
        require_roles("admin", "hod")
    ),
):
    return {
        "message": "Management access granted",
        "role": current_user["role"],
    }