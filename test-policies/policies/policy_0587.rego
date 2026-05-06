package risk.authorization.action.verify.policy_0587

# Auto-generated policy 587 (Rego v1 syntax)
# Package: risk.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0587",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0587_allowed if {
    data.policies.risk.enabled
}
policy_0587_allowed if {
    input.user.active
    input.resource.public
}
policy_0587_allowed if {
    input.user.role == "admin"
}
policy_0587_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
