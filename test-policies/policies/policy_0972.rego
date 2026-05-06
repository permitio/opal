package risk.authorization.context.deny.policy_0972

# Auto-generated policy 972 (Rego v1 syntax)
# Package: risk.authorization.context.deny

# Metadata
metadata := {
    "policy_id": "0972",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0972_allowed if {
    data.policies.risk.enabled
}
default policy_0972_allowed = false
policy_0972_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
