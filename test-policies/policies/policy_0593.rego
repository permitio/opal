package audit.authentication.context.check.core.policy_0593

# Auto-generated policy 593
# Package: audit.authentication.context.check.core

# Metadata
metadata := {
    "policy_id": "0593",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0593_allowed = false
policy_0593_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0593_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
