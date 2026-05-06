package audit.validation.context.check.data.policy_0402

# Auto-generated policy 402 (Rego v1 syntax)
# Package: audit.validation.context.check.data

# Metadata
metadata := {
    "policy_id": "0402",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0402_allowed if {
    input.user.active
    input.resource.public
}
default policy_0402_allowed = false
policy_0402_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0402_allowed if {
    data.policies.audit.enabled
}
