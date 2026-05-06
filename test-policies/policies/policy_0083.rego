package governance.authorization.user.allow.policy_0083

# Auto-generated policy 83 (Rego v1 syntax)
# Package: governance.authorization.user.allow

# Metadata
metadata := {
    "policy_id": "0083",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0083_allowed if {
    data.policies.governance.enabled
}
policy_0083_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0083_allowed if {
    input.user.active
    input.resource.public
}
policy_0083_allowed if {
    input.user.role == "admin"
}
