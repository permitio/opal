package risk.validation.action.deny.policy_0056

# Auto-generated policy 56 (Rego v1 syntax)
# Package: risk.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0056",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0056_allowed if {
    input.user.active
    input.resource.public
}
policy_0056_allowed if {
    data.policies.risk.enabled
}
policy_0056_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
