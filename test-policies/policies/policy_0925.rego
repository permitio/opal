package audit.authorization.context.verify.policy_0925

# Auto-generated policy 925 (Rego v1 syntax)
# Package: audit.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0925",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0925_allowed if {
    data.policies.audit.enabled
}
policy_0925_allowed if {
    input.user.role == "admin"
}
