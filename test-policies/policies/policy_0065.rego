package security.enforcement.context.check.policy_0065

# Auto-generated policy 65 (Rego v1 syntax)
# Package: security.enforcement.context.check

# Metadata
metadata := {
    "policy_id": "0065",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0065_allowed if {
    input.user.active
    input.resource.public
}
default policy_0065_allowed = false
policy_0065_allowed if {
    data.policies.security.enabled
}
policy_0065_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
