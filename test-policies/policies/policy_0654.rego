package security.enforcement.context.allow.policy_0654

# Auto-generated policy 654 (Rego v1 syntax)
# Package: security.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0654",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0654_allowed if {
    input.user.role == "admin"
}
policy_0654_allowed if {
    input.user.active
    input.resource.public
}
