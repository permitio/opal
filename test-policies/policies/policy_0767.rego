package compliance.enforcement.action.check.logic.policy_0767

# Auto-generated policy 767 (Rego v1 syntax)
# Package: compliance.enforcement.action.check.logic

# Metadata
metadata := {
    "policy_id": "0767",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0767_allowed if {
    input.user.active
    input.resource.public
}
policy_0767_allowed if {
    data.policies.compliance.enabled
}
