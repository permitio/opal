package governance.monitoring.policy.check.policy_0846

# Auto-generated policy 846 (Rego v1 syntax)
# Package: governance.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0846",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0846_allowed if {
    data.policies.governance.enabled
}
policy_0846_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0846_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0846_allowed if {
    input.user.role == "admin"
}
