package compliance.validation.policy.allow.logic.policy_0019

# Auto-generated policy 19 (Rego v1 syntax)
# Package: compliance.validation.policy.allow.logic

# Metadata
metadata := {
    "policy_id": "0019",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0019_allowed if {
    input.user.active
    input.resource.public
}
default policy_0019_allowed = false
policy_0019_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0019_allowed if {
    input.user.role == "admin"
}
