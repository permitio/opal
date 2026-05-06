package governance.monitoring.policy.verify.helpers.policy_0238

# Auto-generated policy 238 (Rego v1 syntax)
# Package: governance.monitoring.policy.verify.helpers

# Metadata
metadata := {
    "policy_id": "0238",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0238_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0238_allowed if {
    input.user.role == "admin"
}
