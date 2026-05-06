package governance.authorization.policy.validate.data.policy_0899

# Auto-generated policy 899 (Rego v1 syntax)
# Package: governance.authorization.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0899",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0899_allowed if {
    input.user.active
    input.resource.public
}
policy_0899_allowed if {
    input.user.role == "admin"
}
policy_0899_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
