package security.authentication.context.verify.policy_0067

# Auto-generated policy 67 (Rego v1 syntax)
# Package: security.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0067",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0067_allowed if {
    input.user.active
    input.resource.public
}
policy_0067_allowed if {
    data.policies.security.enabled
}
policy_0067_allowed if {
    input.user.role == "admin"
}
default policy_0067_allowed = false
