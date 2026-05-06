package risk.enforcement.resource.deny.helpers.policy_0848

# Auto-generated policy 848 (Rego v1 syntax)
# Package: risk.enforcement.resource.deny.helpers

# Metadata
metadata := {
    "policy_id": "0848",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0848_allowed if {
    data.policies.risk.enabled
}
default policy_0848_allowed = false
policy_0848_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
