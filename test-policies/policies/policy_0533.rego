package compliance.monitoring.context.allow.helpers.policy_0533

# Auto-generated policy 533 (Rego v1 syntax)
# Package: compliance.monitoring.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0533",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0533_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0533_allowed if {
    input.user.active
    input.resource.public
}
default policy_0533_allowed = false
policy_0533_allowed if {
    data.policies.compliance.enabled
}
