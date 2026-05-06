package access.authorization.context.validate.logic.policy_0362

# Auto-generated policy 362 (Rego v1 syntax)
# Package: access.authorization.context.validate.logic

# Metadata
metadata := {
    "policy_id": "0362",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0362_allowed if {
    input.user.role == "admin"
}
policy_0362_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0362_allowed if {
    data.policies.access.enabled
}
