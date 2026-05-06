package access.enforcement.policy.deny.policy_0706

# Auto-generated policy 706 (Rego v1 syntax)
# Package: access.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0706",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0706_allowed if {
    input.user.role == "admin"
}
default policy_0706_allowed = false
policy_0706_allowed if {
    data.policies.access.enabled
}
policy_0706_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
