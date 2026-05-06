package audit.authentication.user.check.policy_0518

# Auto-generated policy 518 (Rego v1 syntax)
# Package: audit.authentication.user.check

# Metadata
metadata := {
    "policy_id": "0518",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0518_allowed if {
    input.user.active
    input.resource.public
}
policy_0518_allowed if {
    data.policies.audit.enabled
}
