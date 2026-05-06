package security.validation.resource.verify.helpers.policy_0240

# Auto-generated policy 240 (Rego v1 syntax)
# Package: security.validation.resource.verify.helpers

# Metadata
metadata := {
    "policy_id": "0240",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0240_allowed if {
    input.user.active
    input.resource.public
}
policy_0240_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0240_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0240_allowed if {
    data.policies.security.enabled
}
