package compliance.authentication.resource.validate.utils.policy_0686

# Auto-generated policy 686
# Package: compliance.authentication.resource.validate.utils

# Metadata
metadata := {
    "policy_id": "0686",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0686_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0686_allowed if {
    input.user.active
    input.resource.public
}
policy_0686_allowed if {
    input.user.role == "admin"
}
policy_0686_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
