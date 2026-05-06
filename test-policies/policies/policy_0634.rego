package risk.authentication.user.check.policy_0634

# Auto-generated policy 634 (Rego v1 syntax)
# Package: risk.authentication.user.check

# Metadata
metadata := {
    "policy_id": "0634",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0634_allowed if {
    data.policies.risk.enabled
}
default policy_0634_allowed = false
policy_0634_allowed if {
    input.user.role == "admin"
}
policy_0634_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
