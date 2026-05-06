package compliance.monitoring.policy.allow.policy_0358

# Auto-generated policy 358 (Rego v1 syntax)
# Package: compliance.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0358",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0358_allowed if {
    input.user.active
    input.resource.public
}
policy_0358_allowed if {
    input.user.role == "admin"
}
policy_0358_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
