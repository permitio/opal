package security.enforcement.resource.verify.policy_0126

# Auto-generated policy 126 (Rego v1 syntax)
# Package: security.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0126",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0126_allowed if {
    data.policies.security.enabled
}
policy_0126_allowed if {
    input.user.role == "admin"
}
