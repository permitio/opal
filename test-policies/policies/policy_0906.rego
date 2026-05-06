package audit.authentication.context.verify.policy_0906

# Auto-generated policy 906 (Rego v1 syntax)
# Package: audit.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0906",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0906_allowed = false
policy_0906_allowed if {
    data.policies.audit.enabled
}
policy_0906_allowed if {
    input.user.role == "admin"
}
policy_0906_allowed if {
    input.user.active
    input.resource.public
}
