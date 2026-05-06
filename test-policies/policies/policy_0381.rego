package compliance.enforcement.context.allow.policy_0381

# Auto-generated policy 381 (Rego v1 syntax)
# Package: compliance.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0381",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0381_allowed if {
    input.user.role == "admin"
}
default policy_0381_allowed = false
policy_0381_allowed if {
    input.user.active
    input.resource.public
}
