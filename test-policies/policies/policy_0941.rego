package compliance.validation.context.deny.policy_0941

# Auto-generated policy 941 (Rego v1 syntax)
# Package: compliance.validation.context.deny

# Metadata
metadata := {
    "policy_id": "0941",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0941_allowed = false
policy_0941_allowed if {
    input.user.role == "admin"
}
policy_0941_allowed if {
    input.user.active
    input.resource.public
}
policy_0941_allowed if {
    data.policies.compliance.enabled
}
