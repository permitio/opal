package access.validation.resource.check.policy_0046

# Auto-generated policy 46 (Rego v1 syntax)
# Package: access.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0046",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0046_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0046_allowed = false
policy_0046_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0046_allowed if {
    data.policies.access.enabled
}
