package risk.validation.user.check.utils.policy_0997

# Auto-generated policy 997 (Rego v1 syntax)
# Package: risk.validation.user.check.utils

# Metadata
metadata := {
    "policy_id": "0997",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0997_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0997_allowed if {
    data.policies.risk.enabled
}
policy_0997_allowed if {
    input.user.role == "admin"
}
