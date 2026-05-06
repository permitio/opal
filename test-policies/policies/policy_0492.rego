package security.validation.resource.check.policy_0492

# Auto-generated policy 492 (Rego v1 syntax)
# Package: security.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0492",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0492_allowed if {
    input.user.active
    input.resource.public
}
policy_0492_allowed if {
    data.policies.security.enabled
}
policy_0492_allowed if {
    input.user.role == "admin"
}
