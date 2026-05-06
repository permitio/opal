package access.enforcement.resource.deny.policy_0430

# Auto-generated policy 430 (Rego v1 syntax)
# Package: access.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0430",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0430_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0430_allowed = false
policy_0430_allowed if {
    data.policies.access.enabled
}
