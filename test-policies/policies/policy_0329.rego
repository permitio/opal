package compliance.enforcement.action.check.logic.policy_0329

# Auto-generated policy 329 (Rego v1 syntax)
# Package: compliance.enforcement.action.check.logic

# Metadata
metadata := {
    "policy_id": "0329",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0329_allowed = false
policy_0329_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0329_allowed if {
    data.policies.compliance.enabled
}
policy_0329_allowed if {
    input.user.active
    input.resource.public
}
