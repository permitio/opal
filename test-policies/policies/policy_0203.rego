package compliance.validation.action.deny.logic.policy_0203

# Auto-generated policy 203 (Rego v1 syntax)
# Package: compliance.validation.action.deny.logic

# Metadata
metadata := {
    "policy_id": "0203",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0203_allowed if {
    data.policies.compliance.enabled
}
default policy_0203_allowed = false
policy_0203_allowed if {
    input.user.active
    input.resource.public
}
