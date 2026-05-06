package security.authentication.context.verify.policy_0544

# Auto-generated policy 544 (Rego v1 syntax)
# Package: security.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0544",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0544_allowed if {
    input.user.active
    input.resource.public
}
policy_0544_allowed if {
    data.policies.security.enabled
}
