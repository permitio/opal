package compliance.authorization.action.deny.policy_0191

# Auto-generated policy 191 (Rego v1 syntax)
# Package: compliance.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0191",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0191_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0191_allowed if {
    data.policies.compliance.enabled
}
policy_0191_allowed if {
    input.user.active
    input.resource.public
}
policy_0191_allowed if {
    input.user.role == "admin"
}
