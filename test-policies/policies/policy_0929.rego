package security.validation.user.verify.core.policy_0929

# Auto-generated policy 929
# Package: security.validation.user.verify.core

# Metadata
metadata := {
    "policy_id": "0929",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0929_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0929_allowed = false
policy_0929_denied if {
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
