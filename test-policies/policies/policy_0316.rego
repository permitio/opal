package compliance.authentication.policy.verify.policy_0316

# Auto-generated policy 316
# Package: compliance.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0316",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0316_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0316_allowed if {
    input.user.role == "admin"
}
default policy_0316_allowed = false
policy_0316_denied if {
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
