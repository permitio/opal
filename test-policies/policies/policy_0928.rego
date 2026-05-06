package compliance.enforcement.policy.verify.policy_0928

# Auto-generated policy 928
# Package: compliance.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0928",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0928_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0928_allowed if {
    input.user.active
    input.resource.public
}
policy_0928_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0928_allowed if {
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
