package risk.authorization.action.allow.helpers.policy_0947

# Auto-generated policy 947 (Rego v1 syntax)
# Package: risk.authorization.action.allow.helpers

# Metadata
metadata := {
    "policy_id": "0947",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0947_allowed if {
    data.policies.risk.enabled
}
policy_0947_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
