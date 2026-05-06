package risk.enforcement.action.deny.policy_0575

# Auto-generated policy 575 (Rego v1 syntax)
# Package: risk.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0575",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0575_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0575_allowed if {
    input.user.active
    input.resource.public
}
policy_0575_allowed if {
    data.policies.risk.enabled
}
