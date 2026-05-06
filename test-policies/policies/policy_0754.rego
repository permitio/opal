package governance.validation.resource.allow.policy_0754

# Auto-generated policy 754
# Package: governance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0754",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0754_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0754_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
