package security.authentication.policy.verify.core.policy_0213

# Auto-generated policy 213
# Package: security.authentication.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0213",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0213_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0213_allowed = false
policy_0213_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0213_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
