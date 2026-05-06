package governance.authentication.context.verify.policy_0026

# Auto-generated policy 26 (Rego v1 syntax)
# Package: governance.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0026",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0026_allowed if {
    data.policies.governance.enabled
}
policy_0026_allowed if {
    input.user.active
    input.resource.public
}
policy_0026_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0026_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
