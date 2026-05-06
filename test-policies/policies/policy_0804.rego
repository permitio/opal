package audit.enforcement.resource.check.logic.policy_0804

# Auto-generated policy 804
# Package: audit.enforcement.resource.check.logic

# Metadata
metadata := {
    "policy_id": "0804",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0804 {
    input.user.active
    input.resource.public
}
approved_0804 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0804 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
