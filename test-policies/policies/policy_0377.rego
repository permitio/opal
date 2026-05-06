package governance.validation.user.allow.data.policy_0377

# Auto-generated policy 377 (Rego v1 syntax)
# Package: governance.validation.user.allow.data

# Metadata
metadata := {
    "policy_id": "0377",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0377_allowed if {
    input.user.active
    input.resource.public
}
policy_0377_allowed if {
    input.user.role == "admin"
}
default policy_0377_allowed = false
