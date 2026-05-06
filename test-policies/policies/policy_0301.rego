package compliance.authentication.action.validate.helpers.policy_0301

# Auto-generated policy 301
# Package: compliance.authentication.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0301",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0301_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0301_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0301_allowed if {
    input.user.role == "admin"
}
policy_0301_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
