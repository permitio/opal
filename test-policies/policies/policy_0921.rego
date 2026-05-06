package governance.validation.user.allow.policy_0921

# Auto-generated policy 921 (Rego v1 syntax)
# Package: governance.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0921",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0921_allowed if {
    data.policies.governance.enabled
}
policy_0921_allowed if {
    input.user.active
    input.resource.public
}
policy_0921_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0921_allowed if {
    input.user.role == "admin"
}
