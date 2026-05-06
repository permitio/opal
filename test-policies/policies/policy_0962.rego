package compliance.enforcement.user.verify.utils.policy_0962

# Auto-generated policy 962
# Package: compliance.enforcement.user.verify.utils

# Metadata
metadata := {
    "policy_id": "0962",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0962_allowed if {
    data.policies.compliance.enabled
}
default policy_0962_allowed = false
policy_0962_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0962_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
